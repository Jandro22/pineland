"""Build the frozen Afghanistan 2004-2021 violence observation surfaces.

The primary estimand is province-week activity for the state-based dyad
Government of Afghanistan--Taleban. Other actor/conflict strata are retained
explicitly and never silently folded into the Taliban target. District mapping
is a secondary diagnostic based on event coordinates and the frozen COD grid.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, timedelta
from pathlib import Path
import zipfile

import pandas as pd
from shapely import STRtree, points
from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RAW = STUDY / "data" / "raw"
PROCESSED = STUDY / "data" / "processed"
CONFIG = STUDY / "config"
GED = RAW / "ged261-csv.zip"
COD = RAW / "afg_admin_boundaries.geojson.zip"
DESIGN = CONFIG / "study_design.json"
START = date(2004, 1, 1)
END = date(2021, 8, 15)


PROVINCE_ALIASES = {
    "Wardak": "Maidan Wardak",
    "Sari Pul": "Sar-e-Pul",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def province_name_from_ucdp(value: str) -> str:
    if pd.isna(value):
        return None
    name = str(value).strip()
    if name.lower().endswith(" province"):
        name = name[:-9].strip()
    return PROVINCE_ALIASES.get(name, name)


def classify(row: pd.Series) -> str:
    dyad = str(row["dyad_name"])
    side_a = str(row["side_a"])
    violence = int(row["type_of_violence"])
    if violence == 1 and dyad == "Government of Afghanistan - Taleban":
        return "taliban_state"
    if violence == 1 and dyad == "Government of Afghanistan - IS":
        return "is_state"
    if violence == 1 and dyad == "Government of Afghanistan - Hizb-i Islami-yi Afghanistan":
        return "hig_state"
    if violence == 3 and side_a == "Taleban":
        return "taliban_one_sided"
    if violence == 3 and side_a == "IS":
        return "is_one_sided"
    if violence == 3 and side_a == "Government of Afghanistan":
        return "government_one_sided"
    if violence == 2 and "Taleban" in dyad and "IS" in dyad:
        return "taliban_is_nonstate"
    if violence == 1:
        return "other_state"
    if violence == 2:
        return "other_nonstate"
    return "other_one_sided"


def main() -> None:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    temporal_boundary = date.fromisoformat(design["temporal_boundary"])
    held_out_regions = set(design["geographic_holdout"]["selected_region_codes"])
    provinces = pd.read_csv(PROCESSED / "provinces.csv", dtype=str)
    province_by_name = {row.province_name: row for row in provinces.itertuples(index=False)}

    with zipfile.ZipFile(COD) as archive:
        district_features = json.load(archive.open("afg_admin2.geojson"))["features"]
    district_polygons = [shape(feature["geometry"]) for feature in district_features]
    district_ids = [feature["properties"]["adm2_pcode"] for feature in district_features]
    tree = STRtree(district_polygons)

    with zipfile.ZipFile(GED) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        frame = pd.read_csv(io.TextIOWrapper(archive.open(member), encoding="utf-8"), low_memory=False)
    frame["event_date"] = pd.to_datetime(frame["date_start"], errors="raise").dt.date
    events = frame[
        (frame["country"] == "Afghanistan") &
        (frame["event_date"] >= START) & (frame["event_date"] <= END)
    ].copy().reset_index(drop=True)
    if events.empty:
        raise RuntimeError("no Afghanistan GED events in benchmark window")

    events["province_name"] = events["adm_1"].map(province_name_from_ucdp)
    unknown_provinces = sorted(set(events["province_name"].dropna()) - set(province_by_name))
    if unknown_provinces:
        raise RuntimeError(f"unmapped UCDP provinces: {unknown_provinces}")
    events["province_id"] = events["province_name"].map(
        {name: row.province_id for name, row in province_by_name.items()}
    )
    events["region_id"] = events["province_name"].map(
        {name: row.region_id for name, row in province_by_name.items()}
    )

    # Spatial district crosswalk. A high-confidence district observation also
    # requires UCDP where_prec <= 2; less precise points remain available for
    # province-week scoring but are not treated as district-ground truth.
    valid_points = events["longitude"].notna() & events["latitude"].notna()
    mapped_district: list[str | None] = [None] * len(events)
    if valid_points.any():
        indices = events.index[valid_points].to_numpy(dtype=int)
        point_array = points(events.loc[valid_points, "longitude"].to_numpy(dtype=float),
                             events.loc[valid_points, "latitude"].to_numpy(dtype=float))
        pairs = tree.query(point_array, predicate="within")
        for point_index, polygon_index in zip(pairs[0], pairs[1]):
            mapped_district[int(indices[int(point_index)])] = district_ids[int(polygon_index)]
    events["district_id"] = mapped_district
    events["district_high_confidence"] = (
        events["district_id"].notna() & events["where_prec"].fillna(99).astype(float).le(2)
    )
    events["province_scoring_eligible"] = events["province_id"].notna()
    events["stratum"] = events.apply(classify, axis=1)
    events["week_index"] = events["event_date"].map(lambda value: (value - START).days // 7)
    events["week_start"] = events["week_index"].map(lambda index: START + timedelta(days=7 * int(index)))
    events["split"] = events.apply(
        lambda row: (
            "unscored_no_province" if not row["province_scoring_eligible"] else
            "geographic_validation" if row["event_date"] < temporal_boundary and row["region_id"] in held_out_regions else
            "training" if row["event_date"] < temporal_boundary else
            "strict_joint_holdout" if row["region_id"] in held_out_regions else
            "temporal_validation"
        ), axis=1,
    )

    event_columns = [
        "id", "event_date", "week_start", "week_index", "province_id", "province_name", "region_id",
        "district_id", "district_high_confidence", "province_scoring_eligible", "split", "stratum", "type_of_violence",
        "side_a", "side_b", "dyad_name", "conflict_name", "where_prec", "latitude", "longitude",
        "deaths_a", "deaths_b", "deaths_civilians", "deaths_unknown", "best", "low", "high",
    ]
    event_out = events[event_columns].sort_values(["event_date", "id"]).copy()
    event_out.to_csv(PROCESSED / "events_2004_2021.csv", index=False)

    weeks = []
    current = START
    week_index = 0
    while current <= END:
        weeks.append((week_index, current))
        current += timedelta(days=7)
        week_index += 1
    strata = [
        "taliban_state", "is_state", "hig_state", "taliban_one_sided", "is_one_sided",
        "government_one_sided", "taliban_is_nonstate", "other_state", "other_nonstate",
        "other_one_sided",
    ]
    grouped = events[events["province_scoring_eligible"]].groupby(
        ["province_id", "week_index", "stratum"], observed=True
    ).agg(
        event_count=("id", "size"), fatalities=("best", "sum")
    ).reset_index()
    lookup = {
        (row.province_id, int(row.week_index), row.stratum): (int(row.event_count), float(row.fatalities))
        for row in grouped.itertuples(index=False)
    }
    panel_rows = []
    for province in provinces.itertuples(index=False):
        is_geo = province.region_id in held_out_regions
        for index, week_start in weeks:
            late = week_start >= temporal_boundary
            split = ("strict_joint_holdout" if late and is_geo else
                     "temporal_validation" if late else
                     "geographic_validation" if is_geo else "training")
            row = {
                "province_id": province.province_id,
                "province_name": province.province_name,
                "region_id": province.region_id,
                "week_index": index,
                "week_start": week_start.isoformat(),
                "split": split,
                "taliban_state_active": 0,
            }
            total_events = 0
            total_fatalities = 0.0
            for stratum in strata:
                count, fatalities = lookup.get((province.province_id, index, stratum), (0, 0.0))
                row[f"{stratum}_event_count"] = count
                row[f"{stratum}_fatalities"] = fatalities
                total_events += count
                total_fatalities += fatalities
                if stratum == "taliban_state" and count:
                    row["taliban_state_active"] = 1
            row["all_organized_violence_event_count"] = total_events
            row["all_organized_violence_fatalities"] = total_fatalities
            panel_rows.append(row)
    panel = pd.DataFrame(panel_rows)
    panel.to_csv(PROCESSED / "province_week_panel.csv", index=False)

    split_summary = panel.groupby("split", observed=True).agg(
        province_weeks=("province_id", "size"),
        taliban_active_province_weeks=("taliban_state_active", "sum"),
        taliban_state_events=("taliban_state_event_count", "sum"),
        taliban_state_fatalities=("taliban_state_fatalities", "sum"),
    ).reset_index().to_dict(orient="records")
    manifest = {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "start_date": START.isoformat(), "end_date": END.isoformat(),
        "primary_estimand": "province-week any Government of Afghanistan-Taleban state-based event",
        "week_anchor": START.isoformat(),
        "temporal_boundary": temporal_boundary.isoformat(),
        "geographic_holdout_regions": sorted(held_out_regions),
        "events": len(event_out),
        "province_scoring_eligible_events": int(event_out["province_scoring_eligible"].sum()),
        "events_excluded_for_missing_province": int((~event_out["province_scoring_eligible"]).sum()),
        "province_weeks": len(panel),
        "district_high_confidence_events": int(event_out["district_high_confidence"].sum()),
        "stratum_counts": event_out["stratum"].value_counts().sort_index().to_dict(),
        "split_summary": split_summary,
        "source_hashes": {
            "ged261-csv.zip": sha256(GED),
            "afg_admin_boundaries.geojson.zip": sha256(COD),
            "study_design.json": sha256(DESIGN),
            "provinces.csv": sha256(PROCESSED / "provinces.csv"),
        },
        "district_scoring_policy": "secondary only when spatially mapped and UCDP where_prec <= 2",
        "violence_used_as_control_proxy": False,
    }
    (PROCESSED / "event_panel_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
