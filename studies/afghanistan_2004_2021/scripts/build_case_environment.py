"""Build the untuned Afghanistan schema-v3 empirical case environment.

The physical world uses the 401 harmonized COD districts and their named
administrative centers.  Province and humanitarian-region containers are kept
as explicit hierarchy metadata.  Initial Taliban anchors are derived only from
the immediately pre-benchmark 2003 Government of Afghanistan--Taleban UCDP
state-conflict events, mapped spatially into the frozen COD district polygons.
No 2004-2021 benchmark outcome is used in case construction.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
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
DESIGN = CONFIG / "study_design.json"
COD = RAW / "afg_admin_boundaries.geojson.zip"
GED = RAW / "ged261-csv.zip"
OUT = CONFIG / "case_environment.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def preperiod_taliban_anchors(count: int = 8) -> tuple[list[str], dict[str, int]]:
    """Return top 2003 Taliban-conflict COD districts without using study outcomes."""
    with zipfile.ZipFile(COD) as archive:
        features = json.load(archive.open("afg_admin2.geojson"))["features"]
    polygons = [shape(feature["geometry"]) for feature in features]
    pcodes = [feature["properties"]["adm2_pcode"] for feature in features]
    tree = STRtree(polygons)

    with zipfile.ZipFile(GED) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        frame = pd.read_csv(io.TextIOWrapper(archive.open(member), encoding="utf-8"), low_memory=False)
    subset = frame[
        (frame["country"] == "Afghanistan") &
        (frame["year"] == 2003) &
        (frame["dyad_name"] == "Government of Afghanistan - Taleban") &
        (frame["type_of_violence"] == 1) &
        frame["longitude"].notna() & frame["latitude"].notna()
    ].reset_index(drop=True)
    point_array = points(subset["longitude"].to_numpy(dtype=float),
                         subset["latitude"].to_numpy(dtype=float))
    pairs = tree.query(point_array, predicate="within")
    mapping = {int(point_index): pcodes[int(polygon_index)]
               for point_index, polygon_index in zip(pairs[0], pairs[1])}
    if len(mapping) != len(subset):
        missing = len(subset) - len(mapping)
        raise RuntimeError(f"unmapped 2003 Taliban events: {missing}/{len(subset)}")
    counts: dict[str, int] = {}
    for index in range(len(subset)):
        pcode = mapping[index]
        counts[pcode] = counts.get(pcode, 0) + 1
    ordered = sorted(counts, key=lambda pcode: (-counts[pcode], pcode))
    return ordered[:count], dict(sorted(counts.items()))


def main() -> None:
    CONFIG.mkdir(parents=True, exist_ok=True)
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    region_rows = rows(PROCESSED / "regions.csv")
    province_rows = rows(PROCESSED / "provinces.csv")
    district_rows = rows(PROCESSED / "districts.csv")
    center_rows = rows(PROCESSED / "district_centers.csv")
    population_rows = rows(PROCESSED / "population_2004.csv")
    adjacency = json.loads((PROCESSED / "district_adjacency.json").read_text(encoding="utf-8"))
    if (len(region_rows), len(province_rows), len(district_rows), len(center_rows),
            len(population_rows)) != (8, 34, 401, 401, 401):
        raise RuntimeError("unexpected Afghanistan processed geography dimensions")

    population = {row["district_id"]: int(row["population_2004"])
                  for row in population_rows}
    centers = {row["district_id"]: row for row in center_rows}
    if set(population) != {row["district_id"] for row in district_rows} or set(centers) != set(population):
        raise RuntimeError("district population/center registry mismatch")

    containers = []
    for row in sorted(region_rows, key=lambda item: item["region_id"]):
        containers.append({
            "container_id": row["region_id"], "name": row["region_name"],
            "level": "region", "is_geographic_holdout": row["is_geographic_holdout"] == "true",
        })
    for row in sorted(province_rows, key=lambda item: item["province_id"]):
        containers.append({
            "container_id": row["province_id"], "name": row["province_name"],
            "level": "province", "parent_id": row["region_id"],
            "is_geographic_holdout": row["is_geographic_holdout"] == "true",
        })

    districts = []
    localities = []
    for row in sorted(district_rows, key=lambda item: item["district_id"]):
        district_id = row["district_id"]
        center = centers[district_id]
        district_population = population[district_id]
        districts.append({
            "district_id": district_id,
            "name": row["district_name"],
            "population": district_population,
            "container_ids": {"region": row["region_id"], "province": row["province_id"]},
            "terrain": "empirical mixed terrain",
            "urbanization": 0.35,
            "language_pattern": "FS",
            "connectivity": 0.5,
            "role": "harmonized 2004-2021 physical district",
            "unit_type": row["unit_type"],
        })
        capital_level = int(center["capital_level"])
        locality_kind = "city" if capital_level in {0, 1} else "town"
        localities.append({
            "locality_id": center["locality_id"],
            "district_id": district_id,
            "name": center["name"],
            "kind": locality_kind,
            "population": district_population,
            "x_km": float(center["x_km"]),
            "y_km": float(center["y_km"]),
            "administrative_role": "district_headquarters",
            "terrain_friction": 1.0,
            "infrastructure": 0.5,
            "administrative_capacity": 0.5,
            "observability": 0.5,
            "capital_level": capital_level,
        })

    locality_adjacency = {
        f"{district_id}-HQ": [f"{neighbor}-HQ" for neighbor in neighbors]
        for district_id, neighbors in adjacency["neighbors"].items()
    }
    anchors, preperiod_counts = preperiod_taliban_anchors(8)
    payload = {
        "schema_version": "3.0.0",
        "case_id": "afghanistan_2004_2021_untuned_v1",
        "study_id": "afghanistan_2004_2021",
        "construct": (
            "401 harmonized COD districts with named administrative-center localities; "
            "province and humanitarian-region hierarchy retained explicitly"
        ),
        "primary_validation_unit": "province_week",
        "secondary_validation_unit": "district_period_when_crosswalk_high_confidence",
        "geographic_containers": containers,
        "districts": districts,
        "localities": localities,
        "adjacency": locality_adjacency,
        "initial_insurgent_locality_ids": [f"{district_id}-HQ" for district_id in anchors],
        "initial_condition_rule": (
            "eight highest-count COD districts for Government of Afghanistan-Taleban "
            "state-conflict events in calendar year 2003; benchmark period begins 2004-01-01"
        ),
        "preperiod_taliban_state_conflict_counts_2003": preperiod_counts,
        "actor_semantics": {
            "government": "Islamic Republic of Afghanistan state institutions",
            "fdf": "Afghan national security forces aggregate",
            "police": "Afghan police aggregate",
            "insurgent": "Taleban / Taliban movement",
        },
        "neutral_unidentified_inputs": {
            "terrain_friction": 1.0,
            "infrastructure": 0.5,
            "administrative_capacity": 0.5,
            "observability": 0.5,
            "language_pattern": "FS pending independent district language-profile integration",
        },
        "source_hashes": {
            "study_design.json": sha256(DESIGN),
            "source_manifest.json": sha256(PROCESSED / "source_manifest.json"),
            "geography_manifest.json": sha256(PROCESSED / "geography_manifest.json"),
            "population_manifest.json": sha256(PROCESSED / "population_manifest.json"),
            "districts.csv": sha256(PROCESSED / "districts.csv"),
            "district_centers.csv": sha256(PROCESSED / "district_centers.csv"),
            "district_adjacency.json": sha256(PROCESSED / "district_adjacency.json"),
            "population_2004.csv": sha256(PROCESSED / "population_2004.csv"),
            "ged261-csv.zip": sha256(GED),
        },
        "outcome_data_used_for_geography": False,
        "benchmark_period_outcomes_used_for_initialization": False,
        "calibration_licensed": False,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "sha256": sha256(OUT),
        "regions": 8, "provinces": 34, "districts": 401, "localities": 401,
        "initial_taliban_anchors": payload["initial_insurgent_locality_ids"],
        "benchmark_outcomes_used": False,
    }, indent=2))


if __name__ == "__main__":
    main()
