"""Build frozen Afghanistan province-week and high-confidence district-month panels."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile

from shapely import STRtree, points
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RAW = STUDY / "data" / "raw"
OUT = STUDY / "data" / "processed"
DESIGN = STUDY / "config" / "study_design.json"
UCDP = RAW / "ged261-csv.zip"
COD = RAW / "afg_admin_boundaries.geojson.zip"
START = date(2004, 1, 1)
BOUNDARY = date(2015, 1, 1)
END = date(2021, 8, 15)

DYAD_STRATA = {
    (1, "Government of Afghanistan - Taleban"): "taliban_state_based",
    (3, "Taleban - Civilians"): "taliban_one_sided",
    (3, "Government of Afghanistan - Civilians"): "government_one_sided",
    (1, "Government of Afghanistan - IS"): "is_state_based",
    (3, "IS - Civilians"): "is_one_sided",
    (2, "IS - Taleban"): "is_taliban_nonstate",
    (1, "Government of Afghanistan - Hizb-i Islami-yi Afghanistan"): "hizb_state_based",
    (2, "Hizb-i Islami-yi Afghanistan - Taleban"): "hizb_taliban_nonstate",
    (2, "Taleban - High Council of Afghanistan Islamic Emirate"): "taliban_faction_nonstate",
    (2, "High Council of Afghanistan Islamic Emirate, IS - Taleban"): "taliban_faction_nonstate",
    (1, "Government of Afghanistan - High Council of Afghanistan Islamic Emirate"): "taliban_faction_state_based",
    (2, "Forces of Mullah Abdol Rauf Khadim - Taleban"): "taliban_faction_nonstate",
    (1, "Government of United States of America - al-Qaida"): "international_counterterrorism",
    (1, "Government of Pakistan - TTP"): "external_state_based",
    (1, "Government of Afghanistan - Government of Pakistan"): "interstate",
    (2, "Jam'iyyat-i Islami-yi Afghanistan - Junbish-i Milli-yi Islami"): "other_nonstate",
    (2, "Forces of Amanullah Khan  - Forces of Arbab Basir"): "other_nonstate",
    (2, "Forces of Amanullah Khan  - Forces of Ismail Khan"): "other_nonstate",
    (2, "Hizb-i Islami-yi Afghanistan - Jam'iyyat-i Islami-yi Afghanistan"): "other_nonstate",
    (3, "LeJ - Civilians"): "other_one_sided",
    (1, "Government of India - Kashmir insurgents"): "external_state_based",
    (2, "TTP-KM - TTP-SM"): "other_nonstate",
    (1, "Government of Iraq - IS"): "external_state_based",
    (3, "Government of Tajikistan - Civilians"): "external_one_sided",
}
STRATA = tuple(sorted(set(DYAD_STRATA.values())))
KEEP = (
    "id", "relid", "date_start", "date_end", "date_prec", "side_a", "side_b",
    "dyad_name", "type_of_violence", "latitude", "longitude", "where_prec",
    "adm_1", "adm_2", "where_coordinates", "source_article", "source_original",
    "low", "best", "high",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: str) -> str:
    value = re.sub(r"\bprovince\b", " ", value or "", flags=re.I)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def split_label(when: date, held_out: bool) -> str:
    early = when < BOUNDARY
    if early:
        return "geographic_validation" if held_out else "training"
    return "strict_joint_holdout" if held_out else "temporal_validation"


def week_windows():
    cursor = START
    index = 0
    while cursor <= END:
        stop = min(END, cursor + timedelta(days=6))
        yield index, cursor, stop
        cursor = stop + timedelta(days=1)
        index += 1


def month_windows():
    cursor = START.replace(day=1)
    index = 0
    while cursor <= END:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(END, next_month - timedelta(days=1))
        start = max(START, cursor)
        yield index, start, stop
        cursor = next_month
        index += 1


def blank_counts(row: dict) -> None:
    for stratum in STRATA:
        row[f"{stratum}_events"] = 0
        for estimate in ("low", "best", "high"):
            row[f"{stratum}_deaths_{estimate}"] = 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    held_out_regions = set(design["geographic_holdout"]["selected_region_codes"])
    with zipfile.ZipFile(COD) as archive:
        province_features = json.load(archive.open("afg_admin1.geojson"))["features"]
        district_features = json.load(archive.open("afg_admin2.geojson"))["features"]
    province_polygons = [shape(feature["geometry"]) for feature in province_features]
    district_polygons = [shape(feature["geometry"]) for feature in district_features]
    province_tree = STRtree(province_polygons)
    district_tree = STRtree(district_polygons)
    province_rows = [feature["properties"] for feature in province_features]
    district_rows = [feature["properties"] for feature in district_features]
    province_by_id = {row["adm1_pcode"]: row for row in province_rows}
    district_by_id = {row["adm2_pcode"]: row for row in district_rows}
    province_alias = {norm(row["adm1_name"]): row["adm1_pcode"] for row in province_rows}
    province_alias[norm("Wardak")] = next(
        row["adm1_pcode"] for row in province_rows if row["adm1_name"] == "Maidan Wardak"
    )
    province_alias[norm("Sari Pul")] = next(
        row["adm1_pcode"] for row in province_rows if row["adm1_name"] == "Sar-e-Pul"
    )

    weekly = {}
    for province_id, row in province_by_id.items():
        held = row["regioncode"] in held_out_regions
        for index, start, stop in week_windows():
            item = {
                "province_id": province_id, "province_name": row["adm1_name"],
                "region_id": row["regioncode"], "split": split_label(start, held),
                "window_id": f"W{index:04d}", "week_start": start.isoformat(),
                "week_end": stop.isoformat(), "exposure_days": (stop - start).days + 1,
            }
            blank_counts(item)
            weekly[(province_id, index)] = item

    monthly = {}
    for district_id, row in district_by_id.items():
        held = row["regioncode"] in held_out_regions
        for index, start, stop in month_windows():
            item = {
                "district_id": district_id, "district_name": row["adm2_name"],
                "province_id": row["adm1_pcode"], "province_name": row["adm1_name"],
                "region_id": row["regioncode"], "split": split_label(start, held),
                "window_id": f"M{index:03d}", "month_start": start.isoformat(),
                "month_end": stop.isoformat(), "exposure_days": (stop - start).days + 1,
            }
            blank_counts(item)
            monthly[(district_id, index)] = item

    raw_events = []
    with zipfile.ZipFile(UCDP) as archive:
        member = next(name for name in archive.namelist() if name.endswith("GEDEvent_v26_1.csv"))
        with io.TextIOWrapper(archive.open(member), encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                if raw["country"] != "Afghanistan":
                    continue
                when = datetime.fromisoformat(raw["date_start"]).date()
                if START <= when <= END:
                    raw_events.append(raw)
    unknown = sorted({
        (int(raw["type_of_violence"]), raw["dyad_name"])
        for raw in raw_events
        if (int(raw["type_of_violence"]), raw["dyad_name"]) not in DYAD_STRATA
    })
    if unknown:
        raise RuntimeError(f"unreviewed Afghanistan UCDP dyads: {unknown}")

    xs = []; ys = []; valid_indices = []
    for index, raw in enumerate(raw_events):
        try:
            xs.append(float(raw["longitude"])); ys.append(float(raw["latitude"])); valid_indices.append(index)
        except (TypeError, ValueError):
            pass
    province_geometry = {}; district_geometry = {}
    if valid_indices:
        point_array = points(xs, ys)
        for tree, target in ((province_tree, province_geometry), (district_tree, district_geometry)):
            pairs = tree.query(point_array, predicate="within")
            counts = {}
            for point_index, polygon_index in zip(pairs[0], pairs[1]):
                event_index = valid_indices[int(point_index)]
                if event_index in counts:
                    raise RuntimeError(f"event point matched multiple polygons: event_index={event_index}")
                counts[event_index] = int(polygon_index)
            target.update(counts)

    processed = []
    province_fallback = 0
    province_unmapped = 0
    district_high_confidence = 0
    province_geometry_disagreements = 0
    for index, raw in enumerate(raw_events):
        when = datetime.fromisoformat(raw["date_start"]).date()
        stratum = DYAD_STRATA[(int(raw["type_of_violence"]), raw["dyad_name"])]
        fallback = province_alias.get(norm(raw["adm_1"]))
        geometry_province = (province_rows[province_geometry[index]]["adm1_pcode"]
                             if index in province_geometry else "")
        if geometry_province and fallback and geometry_province != fallback:
            province_geometry_disagreements += 1
        if fallback:
            province_id = fallback
            province_method = "ucdp_historical_adm1"
        elif geometry_province:
            province_id = geometry_province
            province_method = "cod_geometry_fallback"
            province_fallback += 1
        else:
            province_id = ""
            province_method = "unmapped"
        if not province_id:
            province_unmapped += 1

        district_id = ""
        district_method = "unmapped_or_low_precision"
        where_prec = int(raw["where_prec"] or 99)
        if index in district_geometry and where_prec <= 2:
            district_id = district_rows[district_geometry[index]]["adm2_pcode"]
            district_method = "geometry_high_confidence"
            district_high_confidence += 1

        if province_id:
            week_index = (when - START).days // 7
            row = weekly[(province_id, week_index)]
            row[f"{stratum}_events"] += 1
            for estimate in ("low", "best", "high"):
                row[f"{stratum}_deaths_{estimate}"] += int(raw[estimate])
        if district_id:
            month_index = (when.year - START.year) * 12 + (when.month - START.month)
            row = monthly[(district_id, month_index)]
            row[f"{stratum}_events"] += 1
            for estimate in ("low", "best", "high"):
                row[f"{stratum}_deaths_{estimate}"] += int(raw[estimate])

        event = {key: raw[key] for key in KEEP}
        event.update({
            "stratum": stratum,
            "province_id": province_id,
            "province_name_harmonized": province_by_id[province_id]["adm1_name"] if province_id else "",
            "province_assignment_method": province_method,
            "district_id": district_id,
            "district_name_harmonized": district_by_id[district_id]["adm2_name"] if district_id else "",
            "district_assignment_method": district_method,
            "district_high_confidence": int(bool(district_id)),
        })
        processed.append(event)

    event_fields = list(KEEP) + [
        "stratum", "province_id", "province_name_harmonized", "province_assignment_method",
        "district_id", "district_name_harmonized", "district_assignment_method",
        "district_high_confidence",
    ]
    with (OUT / "ucdp_afghanistan_events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_fields)
        writer.writeheader(); writer.writerows(processed)
    weekly_rows = list(weekly.values())
    with (OUT / "province_week_panel.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(weekly_rows[0]))
        writer.writeheader(); writer.writerows(weekly_rows)
    monthly_rows = list(monthly.values())
    with (OUT / "district_month_panel.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(monthly_rows[0]))
        writer.writeheader(); writer.writerows(monthly_rows)

    manifest = {
        "schema_version": "1.0.0",
        "ucdp_sha256": digest(UCDP),
        "cod_sha256": digest(COD),
        "study_design_sha256": digest(DESIGN),
        "events": len(processed),
        "events_by_stratum": {stratum: sum(e["stratum"] == stratum for e in processed) for stratum in STRATA},
        "province_week_rows": len(weekly_rows),
        "district_month_rows": len(monthly_rows),
       "province_fallback_assignments": province_fallback,
       "province_unmapped_events": province_unmapped,
       "province_geometry_vs_adm1_disagreements": province_geometry_disagreements,
        "province_assignment_rule": "UCDP historical adm_1 when mapped; COD point geometry only when adm_1 is unavailable",
        "district_high_confidence_events": district_high_confidence,
        "district_high_confidence_share": district_high_confidence / max(1, len(processed)),
        "district_rule": "COD point-in-polygon and UCDP where_prec <= 2",
        "unknown_dyads": [],
        "geographic_holdout_regions": sorted(held_out_regions),
    }
    (OUT / "panel_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
