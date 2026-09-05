"""Derive frozen adjacency, centroids, and area without redistributing polygons."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
SOURCE = STUDY / "data" / "raw" / "gadm41" / "gadm41_NPL_3.json"
DISTRICTS = STUDY / "config" / "districts.csv"
OUT = STUDY / "data" / "processed"
GADM_ALIASES = {
    "Chitawan": "Chitwan", "Dhanusa": "Dhanusha",
    "Kapilbastu": "Kapilvastu", "Tanahu": "Tanahun",
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    registry = {row["district_name"]: row for row in csv.DictReader(DISTRICTS.open(encoding="utf-8"))}
    frame = gpd.read_file(SOURCE)
    frame["district_name"] = frame["NAME_3"].replace(GADM_ALIASES)
    missing = sorted(set(registry) - set(frame["district_name"]))
    extra = sorted(set(frame["district_name"]) - set(registry))
    if len(frame) != 75 or missing or extra:
        raise RuntimeError({"features": len(frame), "missing": missing, "extra": extra})
    frame["district_id"] = frame["district_name"].map(lambda name: registry[name]["district_id"])
    metric = frame.to_crs("EPSG:6933")
    frame["area_km2"] = metric.geometry.area / 1_000_000
    metric_points = metric.geometry.representative_point()
    points = metric_points.to_crs("EPSG:4326")
    frame["centroid_longitude"] = points.x
    frame["centroid_latitude"] = points.y
    frame["x_km"] = (metric_points.x - metric_points.x.min()) / 1_000
    frame["y_km"] = (metric_points.y - metric_points.y.min()) / 1_000

    adjacency: dict[str, list[str]] = {district_id: [] for district_id in frame["district_id"]}
    # GADM contains tiny boundary overlaps, so strict ``touches`` drops real
    # neighbors. Zero boundary distance (within a one-metre numeric tolerance)
    # implements queen contiguity without inventing long-range links.
    for left in range(len(metric)):
        for right in range(left + 1, len(metric)):
            if metric.geometry.iloc[left].distance(metric.geometry.iloc[right]) <= 1.0:
                first, second = frame.iloc[left]["district_id"], frame.iloc[right]["district_id"]
                adjacency[first].append(second)
                adjacency[second].append(first)
    adjacency = {key: sorted(set(values)) for key, values in sorted(adjacency.items())}
    if any(not neighbors for neighbors in adjacency.values()):
        raise RuntimeError(f"queen adjacency produced islands: {[k for k, v in adjacency.items() if not v]}")
    if any(first not in adjacency[second] for first, neighbors in adjacency.items() for second in neighbors):
        raise RuntimeError("adjacency is not symmetric")

    OUT.mkdir(parents=True, exist_ok=True)
    columns = ["district_id", "district_name", "area_km2", "centroid_latitude",
               "centroid_longitude", "x_km", "y_km"]
    frame[columns].sort_values("district_id").to_csv(OUT / "district_geography.csv", index=False)
    (OUT / "district_adjacency.json").write_text(json.dumps({
        "schema_version": "1.0.0",
        "definition": "queen_contiguity_as_boundary_distance_le_1m_on_gadm_4_1_historical_district_polygons",
        "source_sha256": file_hash(SOURCE),
        "neighbors": adjacency,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "districts": len(frame),
        "undirected_edges": sum(map(len, adjacency.values())) // 2,
        "minimum_degree": min(map(len, adjacency.values())),
        "maximum_degree": max(map(len, adjacency.values())),
        "source_sha256": file_hash(SOURCE),
    }, indent=2))


if __name__ == "__main__":
    main()
