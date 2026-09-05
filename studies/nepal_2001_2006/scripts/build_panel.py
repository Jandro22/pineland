"""Transform frozen UCDP rows into a complete 75-district split-week panel."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
SOURCE = STUDY / "data" / "raw" / "ged261" / "GEDEvent_v26_1.csv"
DISTRICTS = STUDY / "config" / "districts.csv"
SPLITS = STUDY / "config" / "split_manifest.json"
PROCESSED = STUDY / "data" / "processed"
START = date(2001, 11, 26)
BOUNDARY = date(2005, 1, 1)
END = date(2006, 11, 21)
STRATA = (
    "government_maoist_state_based",
    "state_one_sided",
    "maoist_one_sided",
)
KEEP = (
    "id", "relid", "date_start", "date_end", "date_prec", "side_a", "side_b",
    "dyad_name", "type_of_violence", "latitude", "longitude", "where_prec",
    "adm_1", "adm_2", "source_article", "source_original", "low", "best", "high",
)


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def source_stratum(row: dict[str, str]) -> str | None:
    key = (int(row["type_of_violence"]), row["dyad_name"])
    mapping = {
        (1, "Government of Nepal - CPN-M"): "government_maoist_state_based",
        (3, "Government of Nepal - Civilians"): "state_one_sided",
        (3, "CPN-M - Civilians"): "maoist_one_sided",
    }
    return mapping.get(key)


def windows(start: date, end: date, label: str):
    cursor = start
    index = 0
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=6))
        yield {
            "window_id": f"{label}-{index:03d}", "start": cursor, "end": stop,
            "exposure_days": (stop - cursor).days + 1,
        }
        cursor = stop + timedelta(days=1)
        index += 1


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    district_rows = list(csv.DictReader(DISTRICTS.open(encoding="utf-8")))
    if len(district_rows) != 75:
        raise RuntimeError(f"expected 75 historical districts, got {len(district_rows)}")
    alias_to_district: dict[str, dict[str, str]] = {}
    for district in district_rows:
        for alias in district["aliases"].split("|") + [district["district_name"]]:
            if alias in alias_to_district:
                raise RuntimeError(f"duplicate district alias: {alias}")
            alias_to_district[alias] = district

    split_windows = list(windows(START, BOUNDARY - timedelta(days=1), "early"))
    split_windows += list(windows(BOUNDARY, END, "late"))
    panel: dict[tuple[str, str], dict[str, object]] = {}
    for district in district_rows:
        eastern = district["is_eastern_holdout"].lower() == "true"
        for window in split_windows:
            early = window["start"] < BOUNDARY
            split = ("geographic_validation" if eastern else "training") if early else (
                "strict_joint_holdout" if eastern else "temporal_validation")
            row: dict[str, object] = {
                "district_id": district["district_id"],
                "district_name": district["district_name"],
                "development_region": district["development_region"],
                "split": split,
                "window_id": window["window_id"],
                "week_start": window["start"].isoformat(),
                "week_end": window["end"].isoformat(),
                "exposure_days": window["exposure_days"],
            }
            for stratum in STRATA:
                row[f"{stratum}_events"] = 0
                for estimate in ("low", "best", "high"):
                    row[f"{stratum}_deaths_{estimate}"] = 0
            panel[(district["district_id"], window["window_id"])] = row

    processed_events: list[dict[str, object]] = []
    unmapped: list[dict[str, str]] = []
    with SOURCE.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw["country"] != "Nepal":
                continue
            event_start, event_end = parse_date(raw["date_start"]), parse_date(raw["date_end"])
            if event_end < START or event_start > END:
                continue
            stratum = source_stratum(raw)
            if stratum is None:
                raise RuntimeError(
                    f"unreviewed Nepal event classification id={raw['id']} "
                    f"type={raw['type_of_violence']} dyad={raw['dyad_name']}"
                )
            district = alias_to_district.get(raw["adm_2"])
            event = {key: raw[key] for key in KEEP}
            event.update({
                "stratum": stratum,
                "district_id": district["district_id"] if district else "",
                "district_name": district["district_name"] if district else "",
                "date_or_location_ambiguous": int(raw["date_prec"] != "1" or
                                                   int(raw["where_prec"]) > 2),
            })
            if district is None:
                unmapped.append(raw)
            else:
                era = "early" if event_start < BOUNDARY else "late"
                era_start = START if era == "early" else BOUNDARY
                index = (event_start - era_start).days // 7
                key = (district["district_id"], f"{era}-{index:03d}")
                panel_row = panel[key]
                panel_row[f"{stratum}_events"] += 1
                for estimate in ("low", "best", "high"):
                    panel_row[f"{stratum}_deaths_{estimate}"] += int(raw[estimate])
            processed_events.append(event)

    event_path = PROCESSED / "ucdp_nepal_events.csv"
    event_fields = list(KEEP) + ["stratum", "district_id", "district_name",
                                 "date_or_location_ambiguous"]
    with event_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_fields)
        writer.writeheader(); writer.writerows(processed_events)
    panel_path = PROCESSED / "district_week_panel.csv"
    panel_rows = list(panel.values())
    with panel_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(panel_rows[0]))
        writer.writeheader(); writer.writerows(panel_rows)
    unmapped_path = PROCESSED / "unmapped_events.json"
    unmapped_path.write_text(json.dumps([
        {key: row[key] for key in ("id", "date_start", "where_prec", "where_coordinates",
                                   "adm_1", "adm_2", "dyad_name")}
        for row in unmapped
    ], indent=2) + "\n", encoding="utf-8")
    summary = {
        "schema_version": "1.0.0",
        "source_sha256": hash_file(SOURCE),
        "district_registry_sha256": hash_file(DISTRICTS),
        "split_manifest_sha256": hash_file(SPLITS),
        "events": len(processed_events),
        "mapped_events": len(processed_events) - len(unmapped),
        "unmapped_events": len(unmapped),
        "districts": len(district_rows),
        "panel_rows": len(panel_rows),
        "explicit_zero_rows": sum(not any(int(row[f"{s}_events"]) for s in STRATA)
                                  for row in panel_rows),
        "partial_exposure_rows": sum(int(row["exposure_days"]) != 7 for row in panel_rows),
        "events_by_stratum": {
            stratum: sum(event["stratum"] == stratum for event in processed_events)
            for stratum in STRATA
        },
    }
    (PROCESSED / "panel_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
