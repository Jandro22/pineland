"""Build an outcome-blind UCDP GED geographic-month panel for a future case."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pandas as pd
from shapely import STRtree, points
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--country", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    case_root = args.case if args.case.is_absolute() else ROOT / args.case
    raw = case_root / "data" / "raw"
    archives = list(raw.glob("ged*.zip"))
    boundaries = list(raw.glob("gadm*.zip"))
    if len(archives) != 1 or len(boundaries) != 1:
        raise SystemExit("expected one GED and one GADM archive")
    with zipfile.ZipFile(archives[0]) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".csv"))
        events = pd.read_csv(io.TextIOWrapper(archive.open(member), encoding="utf-8"), low_memory=False)
    events["event_date"] = pd.to_datetime(events["date_start"], errors="coerce")
    events = events[
        (events["country"] == args.country)
        & (events["event_date"] >= pd.Timestamp(args.start))
        & (events["event_date"] <= pd.Timestamp(args.end))
    ].copy().reset_index(drop=True)
    with zipfile.ZipFile(boundaries[0]) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".json"))
        features = json.load(archive.open(member))["features"]
    polygons = [shape(feature["geometry"]) for feature in features]
    ids = [feature["properties"]["GID_2"] for feature in features]
    tree = STRtree(polygons)
    mapped = [None] * len(events)
    valid = events["longitude"].notna() & events["latitude"].notna()
    if valid.any():
        indices = events.index[valid].to_numpy(dtype=int)
        point_array = points(events.loc[valid, "longitude"].to_numpy(dtype=float), events.loc[valid, "latitude"].to_numpy(dtype=float))
        pairs = tree.query(point_array, predicate="within")
        for point_index, polygon_index in zip(pairs[0], pairs[1]):
            mapped[int(indices[int(point_index)])] = ids[int(polygon_index)]
    events["geography_id"] = mapped
    events = events[events["geography_id"].notna()].copy()
    events["month"] = events["event_date"].dt.to_period("M").astype(str)
    panel = (
        events.groupby(["geography_id", "month"], as_index=False)
        .agg(event_count=("id", "count"), best_fatalities=("best", "sum"), civilian_fatalities=("deaths_civilians", "sum"))
        .sort_values(["month", "geography_id"])
    )
    processed = case_root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    output = processed / f"ucdp_{case_root.name}_geography_month_panel.csv"
    panel.to_csv(output, index=False)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "1.0.0",
        "case_id": case_root.name,
        "status": "partial_not_ready",
        "source": "UCDP Georeferenced Event Dataset",
        "country": args.country,
        "period": {"start": args.start, "end": args.end},
        "rows": len(panel),
        "events_with_geography": len(events),
        "output": output.relative_to(case_root).as_posix(),
        "sha256": digest,
        "missing_artifacts": ["control_presence_panel", "case-specific measurement join"],
    }
    (processed / "panel_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
